# Bordereaux Validator Testing Guide

## Current Status
✅ **Backend Server**: Running on `http://127.0.0.1:8000`
- Validation engine active
- Heatmap color logic implemented (light green → dark red gradient)
- Test pack selection supported

## Setup Steps

### 1. Install Node.js (if not already installed)
The frontend requires Node.js and npm. Install via:
```bash
# Using Homebrew (macOS)
brew install node

# Or download from https://nodejs.org/
```

### 2. Start Frontend Development Server
```bash
cd frontend
npm install  # Run this once to install dependencies
npm start    # Start development server on http://localhost:3000
```

### 3. Start Backend Server
```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Testing in Excel

### Prerequisites
- Excel 2016+ (Desktop version on macOS or Windows)
- OR Excel Online in Microsoft 365

### Method 1: Sideload Add-in (Excel Desktop)

**macOS:**
1. Open Excel
2. Go to **Insert** → **Get Add-ins** → **My Add-ins** → **Upload My Add-in**
3. Select the manifest file: `frontend/manifest.xml`
4. Click **Install**
5. The task pane will appear on the right side

**Windows:**
1. Similar process, but file path will be different

### Method 2: Excel Online (Easiest for Quick Testing)

1. Go to **Office.com** and sign in
2. Open Excel Online
3. Click **Insert** → **Get Add-ins** → **Upload My Add-in**
4. Upload `frontend/manifest.xml`

## Testing Workflow

### Step 1: Prepare Test Data
Create or open a bordereaux file with your data.

### Step 2: Open in Excel and Add-in

1. Open the XLSX file in Excel
2. The task pane should appear on the right
3. You should see:
   - Test Pack dropdown (Bordereaux)
   - Pack Configs (JSON textarea)
   - Validate button

### Step 3: Test Pack Selection & Heatmap

1. **Select a data range** (including headers)
2. **Choose the test pack** from dropdown
3. Click **"Validate Selected Range"**
4. Wait for validation to complete

### Expected Results

- **Heatmap coloring**: All cells should be colored
  - Light green = 0 failures
  - Dark red = maximum failures
  - Gradient between for varying failure counts
- **Header row**: Should NOT be colored (row 1 skipped)
- **Comments**: Only failed cells get comments showing which tests failed

#### Visual Indicators
- Cells with no failures: Light green (#E2F0D9)
- Cells with max failures: Dark red (#C00000)
- Middle gradient: Smooth transition between colors

### Step 4: Verify Comments

1. **Click on a colored cell** (especially red ones)
2. A **comment indicator** should appear
3. **Hover over or click the comment** to see which tests failed
4. Comments only appear on failed cells (not on passing cells)

## Troubleshooting

### Issue: Task Pane doesn't appear
- ✅ Verify frontend dev server is running (`npm start`)
- ✅ Check frontend server output for errors
- ✅ Try hard-refresh in Excel (Ctrl+F5 or Cmd+Shift+R)

### Issue: "Validation failed: Backend error: 404"
- ✅ Verify backend is running: `curl http://127.0.0.1:8000/health`
- ✅ Check backend console output for errors
- ✅ Verify backend URL in task pane is correct

### Issue: Colors not showing or wrong colors
- ✅ Verify `_severity_color()` in `backend/app/validation.py` uses correct gradient
- ✅ Check taskpane.js `heatmapColor()` function matches backend

### Issue: Header row is colored
- ✅ Check that taskpane.js applies colors only when `result.rowIndex > 0`

### Issue: Comments not appearing on failed cells
- ✅ Verify backend returns `failCount > 0` for failed cells
- ✅ Check taskpane.js adds comments only when `failCount > 0`

## Backend Testing (CLI Alternative)

If you prefer to test without Excel UI, use the CLI script:

```bash
cd backend

# Test with bordereaux pack
python scripts/apply_pack_highlighting.py \
  --input ../example/your_bordereaux.xlsx \
  --output ../example/test_output.xlsx \
  --pack bordereaux

# View results
# - Heatmapped cells count
# - Failed cells count
# - Comment count
# - Output file path
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/validation.py` | Heatmap color logic (`_severity_color()`) |
| `backend/app/testpacks/bordereaux.py` | Bordereaux validation rules |
| `frontend/taskpane.html` | Pack selector dropdown |
| `frontend/taskpane.js` | Heatmap application logic, color calculation |
| `backend/app/main.py` | FastAPI `/validate-range` endpoint |

## Notes

- The heatmap gradient is consistent between CLI script and Excel plugin
- Header row exclusion is automatic (rowIndex == 0)
- Colors scale based on maximum failures found in any cell
- Comments appear only on cells that failed tests
