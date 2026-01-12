public struct BoundingBox: Hashable, Sendable {
    public let minLat: Double
    public let minLon: Double
    public let maxLat: Double
    public let maxLon: Double

    public init(minLat: Double, minLon: Double, maxLat: Double, maxLon: Double) {
        self.minLat = minLat
        self.minLon = minLon
        self.maxLat = maxLat
        self.maxLon = maxLon
    }
}

