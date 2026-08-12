# Screenshot slots

The interface figures in the guide are **drawings**, not screenshots. They show
the layout and what to look at without pretending to be a capture of a running
system.

To replace any of them with a real screenshot of your own stack, drop a PNG in
this folder using the file name below and rebuild. The document picks it up
automatically (`\IfFileExists`); no LaTeX edit needed. Remove the PNG and the
drawing comes back.

| File name | What to capture | Where |
|---|---|---|
| `swagger.png` | The endpoint list, ideally with one route expanded | `http://api.localhost/docs` |
| `minio.png` | The `profplan` bucket with a few ingested objects | `http://localhost:9001` |
| `flower.png` | The task list, ideally including one FAILURE or RETRY | `http://localhost:5555` |
| `grafana.png` | A dashboard, or Explore showing logs with a `trace_id` | `http://localhost:3000` |

Tips for captures that stay readable when printed:

- Capture at a wide window (≈1600 px) and crop to the panel that matters. A
  full 4K desktop screenshot scaled to page width is unreadable.
- Light theme reads better on paper. Grafana: profile menu → Preferences → Light.
- Blur or use throwaway data for anything with a real email address in it.

To produce something worth capturing in Flower, upload a document with the LLM
providers unreachable, since the retry and failure states are the interesting part.
