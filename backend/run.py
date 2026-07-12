import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    environment = os.environ.get("ENVIRONMENT", "development")
    reload = environment == "development"
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload, env_file=".env")
