# Google API Setup

## 1. Create a Google Cloud project
1. Open the Google Cloud Console.
2. Create a new project or select an existing one.
3. Open `APIs & Services`.

## 2. Enable the right API
1. Click `Library`.
2. Search for `Geocoding API`.
3. Enable it.

You do not need `Places API` for this version. That can be enabled later if we add autocomplete.

## 3. Create an API key
1. Go to `APIs & Services > Credentials`.
2. Click `Create credentials`.
3. Choose `API key`.
4. Copy the key and store it immediately.

## 4. Restrict the key
Recommended setup:
- Application restriction:
  - local development: unrestricted temporarily if needed
  - production backend/MCP: restrict by server IP addresses
- API restriction:
  - restrict to `Geocoding API`

If you later use Google directly in frontend JavaScript, create a second key for that case and restrict it by HTTP referrer. Do not reuse the backend key in public code.

## 5. Add the key locally
Create a `.env` file inside [`Demo`](/Users/camilagoulartlima/Documents/surfspot-finder/Demo) with:

```env
GOOGLE_MAPS_API_KEY=your_google_key_here
```

Optional:

```env
GOOGLE_GEOCODING_BASE_URL=https://maps.googleapis.com/maps/api/geocode/json
```

## 6. Load the key in your shell
If you are not using a dotenv loader yet, export it manually before running the app:

```bash
export GOOGLE_MAPS_API_KEY="your_google_key_here"
python app.py
```

## 7. Production setup
1. Open your deploy provider settings.
2. Add `GOOGLE_MAPS_API_KEY` as an environment variable.
3. Redeploy or restart the service.
4. Confirm logs do not print the key value.

## 8. Quick verification
Once the app is running:
1. Type a valid city like `Florianopolis` and submit.
2. Click `Use my location` and allow browser access.
3. Confirm the selected location summary shows a resolved Google address.
