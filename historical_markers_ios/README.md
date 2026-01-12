# Texas Historical Markers (iOS) — starter plan + code skeleton

This folder contains an **Xcode-ready SwiftUI skeleton** (and a small Swift Package) for an iOS app that:

- Shows a **MapKit map** with **Texas historical marker pins** within the visible map bounds
- Lets you **tap a pin** for a short summary + more details
- When tracking is enabled, **pings + reads a short summary** when you drive near a marker

## Why it’s structured this way

- **Map pins**: fetched by **map bounding box** (fast, scalable)
- **Proximity alerts**: handled via a rolling set of **iOS geofences**
  - iOS limits geofencing to ~20 monitored regions, so the app continuously re-selects the closest markers as you drive.
- **No-offline requirement**: the app can fetch markers on demand; optional caching is included as a simple in-memory store in the skeleton.

## Data source: Texas Historical Commission (THC)

The goal is to use the **Texas Historical Commission historical markers dataset**. In practice, THC often publishes GIS layers via an **ArcGIS FeatureServer** (or similar).

Because this environment can’t access external sites to auto-discover the URL, you will do this once:

1. Find the THC “Historical Markers” GIS/open-data page.
2. Copy the **Feature Layer** endpoint URL that looks like:
   - `https://.../arcgis/rest/services/.../FeatureServer/0`
3. Paste it into the app config (see below).

## What you need to do in Xcode (iOS-only)

1. Create a new Xcode project:
   - **iOS App** (SwiftUI)
   - iOS 17+ recommended
2. Add the Swift Package in `historical_markers_ios/HistoricalMarkersKit/`:
   - Xcode → File → Add Packages… → “Add Local…”
3. Copy the files in `historical_markers_ios/AppSkeleton/` into your app target.
4. Set your THC FeatureServer URL in `MarkerService` (see `AppSkeleton/Config.swift`).
5. Add iOS permissions to your app’s `Info.plist`:
   - `NSLocationWhenInUseUsageDescription`
   - `NSLocationAlwaysAndWhenInUseUsageDescription`
   - `NSLocationAlwaysUsageDescription` (older; still sometimes referenced)
6. Enable Background Modes (Signing & Capabilities):
   - **Location updates** (for better reliability)

## Expected behavior (MVP)

- **Map screen** shows pins within the current map view.
- **Tracking toggle**:
  - When ON, the app monitors nearby markers with geofences.
  - On entering a marker’s geofence, the app plays a short chime and reads a 1–2 sentence summary.
- **No-repeat logic**: the same marker won’t announce again for 24 hours (configurable).

## Files in here

- `HistoricalMarkersKit/`: reusable Swift Package (models + ArcGIS query client + geofence + speech helpers)
- `AppSkeleton/`: SwiftUI app-layer wiring you can drop into an Xcode app target
- `scripts/export_thc_markers.py`: optional helper to export/transform ArcGIS marker data to a compact JSON format

