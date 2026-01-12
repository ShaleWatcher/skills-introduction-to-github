// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "HistoricalMarkersKit",
    platforms: [
        .iOS(.v16)
    ],
    products: [
        .library(
            name: "HistoricalMarkersKit",
            targets: ["HistoricalMarkersKit"]
        )
    ],
    targets: [
        .target(
            name: "HistoricalMarkersKit",
            dependencies: []
        ),
        .testTarget(
            name: "HistoricalMarkersKitTests",
            dependencies: ["HistoricalMarkersKit"]
        ),
    ]
)

