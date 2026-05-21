#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"
#include "GlytchTypes.generated.h"

UENUM(BlueprintType)
enum class EGlytchCompanionType : uint8
{
	FieldGuide,
	AtmosphereVoice,
	DataSteward,
	ArchitecturalEnvisioner,
	CinematicDirector,
	OrderChronicler,
	Unknown
};

UENUM(BlueprintType)
enum class EGlytchOrderName : uint8
{
	PinkOpaque,
	CradleMold,
	SignalChoir,
	Unknown
};

USTRUCT(BlueprintType)
struct FGlytchBoundsMeters
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MinX = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MinY = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MaxX = 4652.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MaxY = 3923.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MinZ = -2.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Bounds")
	float MaxZ = 84.0f;
};

USTRUCT(BlueprintType)
struct FGlytchMarkerDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Markers")
	FName Id;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Markers")
	EGlytchCompanionType CompanionType = EGlytchCompanionType::Unknown;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Markers")
	FVector LocalMeters = FVector::ZeroVector;
};

USTRUCT(BlueprintType)
struct FGlytchOrderOverlayDefinition
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	FName Id;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	EGlytchOrderName OrderName = EGlytchOrderName::Unknown;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	FVector LocalMeters = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	float ExtentMeters = 400.0f;
};

USTRUCT(BlueprintType)
struct FGlytchBuildingMetadataRow : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString UniqueId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	int32 SourceObjectId = 0;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString Type;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	int32 YearUpdate = 0;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float ShapeAreaM2 = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float ShapeLengthM = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float HeightP50 = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float HeightP90 = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float HeightMax = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float GroundZ = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	float EstimatedHeight = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	int32 PointCountInside = 0;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString SourceQuality;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString RoofComplexityScore;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString OrderAffinity;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString ClaimStatus;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FVector CentroidLocalMeters = FVector::ZeroVector;
};
