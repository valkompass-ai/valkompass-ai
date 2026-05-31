# 05. Client-Side Profile

## Research

- Current chat state is held in React state and does not persist.
- A valkompass experience needs issue weights, stance notes, saved comparisons, and source preferences.
- Political preferences should stay client-side only.

## Plan

1. Define a local profile schema.
2. Store the profile in browser storage.
3. Add import and export as JSON.
4. Add a delete local profile action.
5. Send only the profile slice needed for the current request.
6. Keep profile contents out of analytics.
