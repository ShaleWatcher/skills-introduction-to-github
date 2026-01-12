import CoreLocation

public struct HistoricalMarker: Identifiable, Codable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let summary: String
    public let details: String?
    public let latitude: Double
    public let longitude: Double

    public init(
        id: String,
        title: String,
        summary: String,
        details: String? = nil,
        latitude: Double,
        longitude: Double
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.details = details
        self.latitude = latitude
        self.longitude = longitude
    }

    public var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

