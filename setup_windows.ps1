# Create virtual environment
python -m venv .venv

# Upgrade pip
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# Install project and development dependencies
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Setup complete!"
Write-Host "Activate the environment with:"
Write-Host ".\.venv\Scripts\Activate.ps1"