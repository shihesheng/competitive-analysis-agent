# API

Default backend URL:

```text
http://localhost:8000
```

## Main Flow

1. `POST /api/analysis/start`
2. `GET /api/analysis/{task_id}/status`
3. `GET /api/analysis/{task_id}/trace`
4. `GET /api/analysis/{task_id}/quality`
5. `GET /api/analysis/{task_id}/report`

## Start Request

```json
{
  "industry_key": "gaming_mouse",
  "target_platform": "G Pro X Superlight 2",
  "competitors": ["G Pro X Superlight 2", "Viper V3 Pro"],
  "analysis_scene": "gaming mouse product comparison",
  "target_user": "gaming peripheral buyer",
  "time_range": "last two years",
  "focus_dimensions": [],
  "selected_products": [
    {"id": "logitech-gpx-superlight-2"},
    {"id": "razer-viper-v3-pro"}
  ]
}
```

Unknown free-text inputs are allowed. If they are not found in the local product JSON, CollectorAgent marks product resolution and official specs as pending for future search/official-site MCP.

## Final Report

The report endpoint returns `GamingMouseFinalReportSchema`:

- `product_identification`
- `hardware_specs`
- `hardware_fact_comparison`
- `feature_tree`
- `pricing_model`
- `user_persona`
- `evidence_links`
- `score_flow`
- `agent_contributions`
- `pending_data`
- `risk_flags`
- `quality_status`
- `final_recommendation`

Legacy broad-report fields are intentionally removed.
