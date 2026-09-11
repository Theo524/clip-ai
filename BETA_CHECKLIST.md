# Clip AI v20.1 beta checklist

Run this before sharing a build with another tester.

## Startup

- [ ] Backend starts without a traceback.
- [ ] Frontend opens at `http://localhost:3000`.
- [ ] `/status` shows the required checks as Ready.
- [ ] The welcome tour appears once on a fresh browser profile.

## Analysis

- [ ] Upload a 2–5 minute talking-head video.
- [ ] Progress moves through audio/transcription/ranking stages.
- [ ] Best 3 and More suggestions appear.
- [ ] Cancel works during a long task without leaving a fake finished file.

## Rendering

- [ ] Create one Auto Short.
- [ ] Create one Focus + Cinematic Short.
- [ ] Create one Viral Pop Short and check word timing/ghosting.
- [ ] Test a two-person clip and confirm the virtual camera is not constantly micro-panning.
- [ ] Re-render the same exact settings and confirm cached work is reused.

## Projects and export

- [ ] Reopen the project from Projects.
- [ ] Edit/save a generated title and post caption.
- [ ] Download the Short with a human-readable filename.
- [ ] Suggested cover frame loads.
- [ ] Project storage size is visible.

## Cleanup

- [ ] Open System and run Clean temporary files.
- [ ] Finished projects/renders remain intact.
- [ ] Delete a disposable test project and confirm its local storage is removed.
