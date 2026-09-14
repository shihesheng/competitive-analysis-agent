import uvicorn
from pathlib import Path

from dotenv import load_dotenv

from api.routes import app

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

if __name__ == "__main__":
    uvicorn.run("api.routes:app", host="0.0.0.0", port=8000, reload=True)
