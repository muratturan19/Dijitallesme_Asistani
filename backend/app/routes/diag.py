# -*- coding: utf-8 -*-
from fastapi import APIRouter
import subprocess
import pytesseract

router = APIRouter(prefix="/diag", tags=["Diagnostics"])


@router.get("/tesseract")
async def diag_tesseract():
    """Return runtime information about the Tesseract installation."""
    cmd = pytesseract.pytesseract.tesseract_cmd

    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"cmd": cmd, "rc": None, "out": "", "err": "tesseract not found"}

    return {
        "cmd": cmd,
        "rc": result.returncode,
        "out": result.stdout.strip(),
        "err": result.stderr.strip(),
    }
