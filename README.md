# WorkEye Backend

This repository contains the Flask-based backend for the WorkEye project.

## Environment Variables

Configuration is read from a `.env` file (see `.env` in the project root or `env.example`).

### Required variables

- `DATABASE_URL` – PostgreSQL connection string
- `SECRET_KEY`, `JWT_SECRET` – secrets for sessions and JWT tokens

### Screenshots & Cloudinary

To enable screenshot uploads to Cloudinary add the following to your `.env`:

```dotenv
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key   # needs Admin or upload permissions
CLOUDINARY_API_SECRET=your_secret
```

Once set, incoming tracker data that contains a screenshot will be converted to WebP,
uploaded to Cloudinary, and the returned URL stored in the `screenshots` database table.
Local filesystem saving is still controlled via `SAVE_SCREENSHOTS_TO_FS` and related flags.

## Installation

```powershell
cd WorkEye-Project-Backend
python -m venv venv
venv\Scripts\Activate.ps1   # or .\venv\Scripts\activate on cmd
pip install -r requirements.txt
```

## Running

```powershell
python app.py
```

The server listens on port `10000` by default (see `PORT`).


---

For more details, look at individual modules such as `tracker_routes.py` and `cloudinary_helper.py`.