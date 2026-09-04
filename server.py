import os
import tempfile
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from agent import normalize_sources, run_reconciliation
from main import export_reconciliation_csv

app = FastAPI(title="Mint&Match API")

# adding the middleware so that browser can talk to FASTAPI without blocking it.
app.add_middleware(
    CORSMiddleware, 
    allow_credentials=True, 
    allow_origins=["*"],
    allow_headers=["*"], 
    allow_methods=["*"]
)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy", 
        "service": "Mint&Match"
    }

@app.post("/api/reconcile")
async def reconcile(
    bank_file: Optional[UploadFile] = File(None),
    gpay_file: Optional[UploadFile] = File(None),
    use_sample: str = Form("false")
):
    # Determine input files
    if use_sample.lower() == "true" or not bank_file or not gpay_file:
        bank_path = "data/bank_statement_v3.csv"
        gpay_path = "data/gpay_history_v3.csv"
    else:
        # Save uploaded files temporarily to disk
        temp_dir = tempfile.mkdtemp()
        bank_path = os.path.join(temp_dir, bank_file.filename or "bank.csv")
        gpay_path = os.path.join(temp_dir, gpay_file.filename or "gpay.csv")
    
        with open(bank_path, "wb") as f:
            f.write(await bank_file.read())
        
        with open(gpay_path, "wb") as f:
            f.write(await gpay_file.read())
    
    bank_df, gpay_df = normalize_sources(bank_path, gpay_path, save_outputs=False)
    bank_records = bank_df.to_dict(orient="records")
    gpay_records = gpay_df.to_dict(orient="records")
    
    # Run the langgraph reconcile agent
    final_state = run_reconciliation(bank_records=bank_records, gpay_records=gpay_records)
    
    # Export CSV report for download
    os.makedirs("output", exist_ok=True)
    export_reconciliation_csv(final_state, "output/reconciliation_report.csv")
    
    # Return the exact response shape expected by frontend/app.js
    return {
        "stats": final_state.get("stats", {}),
        "confirmed_matches": final_state.get("confirmed_matches", []),
        "exceptions": final_state.get("exceptions", []),
    }

@app.get("/api/download-report")
def download_report():
    csv_path = "output/reconciliation_report.csv"
    if os.path.exists(csv_path):
        return FileResponse(
            csv_path,
            media_type="text/csv",
            filename="reconciliation_report.csv"
        )
    return {"error": "Report not found. Please run reconciliation first."}

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn as uv
    uv.run("server:app", host="127.0.0.1", port=8000, reload=True)
