from typing import List, Optional

from pydantic import BaseModel, Field


class SimulationSection(BaseModel):
    duration: float = Field(..., ge=1, le=3600)
    timeStep: float = Field(0.1, gt=0, le=1.0)
    warmupTime: float = Field(30.0, ge=0)
    randomSeed: Optional[int] = Field(None, ge=0)
    snapshotFrequency: float = Field(10.0, gt=0, le=60)


class DirectionalSplit(BaseModel):
    north: float = Field(..., ge=0, le=1)
    south: float = Field(..., ge=0, le=1)
    east: float = Field(..., ge=0, le=1)
    west: float = Field(..., ge=0, le=1)


class TurnProbabilities(BaseModel):
    left: float = Field(..., ge=0, le=1)
    straight: float = Field(..., ge=0, le=1)
    right: float = Field(..., ge=0, le=1)


class TrafficSection(BaseModel):
    totalVehicles: int = Field(200, gt=0, le=5000)
    arrivalRate: float = Field(0.5, gt=0, le=10.0)
    arrivalDistribution: str = Field("poisson")
    directionalSplit: Optional[DirectionalSplit] = None
    turnProbabilities: Optional[TurnProbabilities] = None


class IntersectionCenter(BaseModel):
    x: float = Field(0.0)
    y: float = Field(0.0)


class GeometrySection(BaseModel):
    intersectionType: str
    intersectionCenter: Optional[IntersectionCenter] = None


class ApproachItem(BaseModel):
    direction: str
    lanes: Optional[int] = Field(None, ge=1, le=4)
    speedLimit: Optional[float] = Field(None, gt=0)


class RoadsSection(BaseModel):
    approachLength: float = Field(200.0, gt=50, le=1000)
    laneWidth: float = Field(3.5, gt=2.5, le=5.0)
    lanesPerApproach: int = Field(2, ge=1, le=4)
    speedLimit: float = Field(13.89, gt=0, le=30.0)
    approaches: Optional[List[ApproachItem]] = None


class MinMaxRange(BaseModel):
    min: float = Field(..., gt=0)
    max: float = Field(..., gt=0)


class VehicleGenerationSection(BaseModel):
    vehicleLength: Optional[MinMaxRange] = None
    vehicleWidth: Optional[MinMaxRange] = None
    desiredSpeed: Optional[MinMaxRange] = None
    maxAcceleration: float = Field(2.0, gt=0)
    comfortDeceleration: float = Field(3.0, gt=0)
    minimumGap: float = Field(2.0, gt=0)
    desiredTimeHeadway: float = Field(1.5, gt=0)
    idmDelta: float = Field(4.0, gt=0)


class ControllerSection(BaseModel):
    greenTime: float = Field(30.0, gt=5, le=120)
    leftDuration: float = Field(5.0, gt=0, le=60)
    yellowTime: float = Field(4.0, gt=2, le=8)
    allRedTime: float = Field(2.0, ge=0, le=5)
    phaseSequence: List[str] = Field(
        default_factory=lambda: [
            "ns_green",
            "ns_yellow",
            "all_red",
            "ew_green",
            "ew_yellow",
            "all_red",
        ]
    )
    offset: float = Field(0.0, ge=0)
    innerRadius: float = Field(10.0, gt=5, le=50)
    outerRadius: float = Field(20.0, gt=5)
    circulatingLanes: int = Field(1, ge=1, le=3)
    criticalGap: float = Field(4.0, gt=0, le=10.0)
    followUpTime: float = Field(2.5, gt=0)
    entrySpeed: float = Field(5.0, gt=0)
    circulatingSpeed: float = Field(8.0, gt=0, le=15.0)


class MetricsSection(BaseModel):
    enabled: Optional[List[str]] = None
    updateFrequency: float = Field(1.0, gt=0)
    rollingWindowSize: float = Field(60.0, gt=0)
    waitSpeedThreshold: float = Field(0.5, ge=0)
    stopSpeedThreshold: float = Field(0.1, ge=0)


class VisualizationSection(BaseModel):
    canvasWidth: int = Field(800, gt=400)
    canvasHeight: int = Field(800, gt=400)
    pixelsPerMeter: float = Field(3.0, gt=0)
    showVehicleIds: bool = Field(False)
    showQueueLengths: bool = Field(True)
    colorScheme: str = Field("default")
    trailLength: int = Field(0, ge=0)


class ScenarioConfiguration(BaseModel):
    simulation: SimulationSection
    traffic: Optional[TrafficSection] = None
    geometry: GeometrySection
    roads: Optional[RoadsSection] = None
    vehicleGeneration: Optional[VehicleGenerationSection] = None
    controller: Optional[ControllerSection] = None
    metrics: Optional[MetricsSection] = None
    visualization: Optional[VisualizationSection] = None
