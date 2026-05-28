#include "GlytchTileManager.h"

#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "GlytchBuildingActor.h"
#include "GlytchBuildingMetadataComponent.h"
#include "GlytchClaimMarkerActor.h"
#include "GlytchCompanionMarkerActor.h"
#include "GlytchOrderOverlayComponent.h"
#include "GlytchTileDataAsset.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	float JsonNumber(const TSharedPtr<FJsonObject>& Object, const TCHAR* FieldName)
	{
		double Value = 0.0;
		return Object.IsValid() && Object->TryGetNumberField(FieldName, Value) ? static_cast<float>(Value) : 0.0f;
	}

	int32 JsonInt(const TSharedPtr<FJsonObject>& Object, const TCHAR* FieldName)
	{
		return FMath::RoundToInt(JsonNumber(Object, FieldName));
	}

	FString JsonString(const TSharedPtr<FJsonObject>& Object, const TCHAR* FieldName)
	{
		FString Value;
		if (Object.IsValid())
		{
			Object->TryGetStringField(FieldName, Value);
		}
		return Value;
	}

	FGlytchBuildingMetadataRow RowFromJson(const TSharedPtr<FJsonObject>& Object)
	{
		FGlytchBuildingMetadataRow Row;
		Row.UniqueId = JsonString(Object, TEXT("uniqueid"));
		Row.SourceObjectId = JsonInt(Object, TEXT("source_objectid"));
		Row.Type = JsonString(Object, TEXT("type"));
		Row.YearUpdate = JsonInt(Object, TEXT("year_update"));
		Row.ShapeAreaM2 = JsonNumber(Object, TEXT("shape_area_m2"));
		Row.ShapeLengthM = JsonNumber(Object, TEXT("shape_length_m"));
		Row.HeightP50 = JsonNumber(Object, TEXT("height_p50"));
		Row.HeightP90 = JsonNumber(Object, TEXT("height_p90"));
		Row.HeightMax = JsonNumber(Object, TEXT("height_max"));
		Row.GroundZ = JsonNumber(Object, TEXT("ground_z"));
		Row.EstimatedHeight = JsonNumber(Object, TEXT("estimated_height"));
		Row.PointCountInside = JsonInt(Object, TEXT("point_count_inside"));
		Row.SourceQuality = JsonString(Object, TEXT("source_quality"));
		Row.RoofComplexityScore = JsonString(Object, TEXT("roof_complexity_score"));
		Row.OrderAffinity = JsonString(Object, TEXT("order_affinity"));
		Row.ClaimStatus = JsonString(Object, TEXT("claim_status"));
		Row.CentroidLocalMeters = FVector(
			JsonNumber(Object, TEXT("centroid_local_x")),
			JsonNumber(Object, TEXT("centroid_local_y")),
			JsonNumber(Object, TEXT("centroid_local_z")));
		return Row;
	}
}

AGlytchTileManager::AGlytchTileManager()
{
	PrimaryActorTick.bCanEverTick = false;

	BuildingActorClass = AGlytchBuildingActor::StaticClass();
	CompanionMarkerClass = AGlytchCompanionMarkerActor::StaticClass();
	ClaimMarkerClass = AGlytchClaimMarkerActor::StaticClass();

	GroundProxyComponent = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("GroundProxy"));
	SetRootComponent(GroundProxyComponent);
	GroundProxyComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GroundProxyComponent->SetHiddenInGame(false);

	WaterProxyComponent = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WaterProxy"));
	WaterProxyComponent->SetupAttachment(RootComponent);
	WaterProxyComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	WaterProxyComponent->SetHiddenInGame(false);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlaneMesh(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (PlaneMesh.Succeeded())
	{
		GroundProxyComponent->SetStaticMesh(PlaneMesh.Object);
		WaterProxyComponent->SetStaticMesh(PlaneMesh.Object);
	}
}

void AGlytchTileManager::BeginPlay()
{
	Super::BeginPlay();

	if (bSpawnOnBeginPlay)
	{
		RebuildTile();
	}
}

void AGlytchTileManager::RebuildTile()
{
	ClearRuntimeActors();

	if (!TileData)
	{
		UE_LOG(LogTemp, Warning, TEXT("GlytchTileManager has no TileData assigned."));
		return;
	}

	TileData->bUsePreviewMetadata = bLoadPreviewMetadata;
	TileData->LoadManifest();
	LoadBuildingMetadata();
	CreateProxyPlanes();
	SpawnBuildings();
	SpawnCompanionMarkers();
	SpawnOrderOverlays();
	SpawnClaimMarkers();

	UE_LOG(LogTemp, Display, TEXT("GlytchTileManager spawned %d buildings, %d markers, %d order overlays, %d claim markers."),
		SpawnedBuildings.Num(), SpawnedMarkers.Num(), SpawnedOverlayActors.Num(), SpawnedClaimMarkers.Num());
}

void AGlytchTileManager::SetMassesVisible(bool bVisible)
{
	for (AGlytchBuildingActor* Building : SpawnedBuildings)
	{
		if (Building)
		{
			Building->SetActorHiddenInGame(!bVisible);
		}
	}
}

void AGlytchTileManager::SetCompanionMarkersVisible(bool bVisible)
{
	for (AGlytchCompanionMarkerActor* Marker : SpawnedMarkers)
	{
		if (Marker)
		{
			Marker->SetActorHiddenInGame(!bVisible);
		}
	}
}

void AGlytchTileManager::SetOrderOverlaysVisible(bool bVisible)
{
	for (AActor* Overlay : SpawnedOverlayActors)
	{
		if (Overlay)
		{
			Overlay->SetActorHiddenInGame(!bVisible);
		}
	}
}

void AGlytchTileManager::SetClaimMarkersVisible(bool bVisible)
{
	for (AGlytchClaimMarkerActor* Marker : SpawnedClaimMarkers)
	{
		if (Marker)
		{
			Marker->SetActorHiddenInGame(!bVisible);
		}
	}
}

void AGlytchTileManager::SetGroundProxyVisible(bool bVisible)
{
	if (GroundProxyComponent)
	{
		GroundProxyComponent->SetHiddenInGame(!bVisible);
	}
}

void AGlytchTileManager::SetWaterProxyVisible(bool bVisible)
{
	if (WaterProxyComponent)
	{
		WaterProxyComponent->SetHiddenInGame(!bVisible);
	}
}

void AGlytchTileManager::SetPointEvidenceVisible(bool bVisible)
{
	UE_LOG(LogTemp, Display, TEXT("Point evidence layer toggled %s. Renderer is intentionally deferred for Phase 3."), bVisible ? TEXT("on") : TEXT("off"));
}

bool AGlytchTileManager::FindMetadata(FName UniqueId, FGlytchBuildingMetadataRow& OutMetadata) const
{
	if (const FGlytchBuildingMetadataRow* Row = MetadataByUniqueId.Find(UniqueId))
	{
		OutMetadata = *Row;
		return true;
	}
	return false;
}

void AGlytchTileManager::ClearRuntimeActors()
{
	for (AGlytchBuildingActor* Building : SpawnedBuildings)
	{
		if (Building)
		{
			Building->Destroy();
		}
	}
	SpawnedBuildings.Reset();

	for (AGlytchCompanionMarkerActor* Marker : SpawnedMarkers)
	{
		if (Marker)
		{
			Marker->Destroy();
		}
	}
	SpawnedMarkers.Reset();

	for (AActor* Overlay : SpawnedOverlayActors)
	{
		if (Overlay)
		{
			Overlay->Destroy();
		}
	}
	SpawnedOverlayActors.Reset();

	for (AGlytchClaimMarkerActor* Marker : SpawnedClaimMarkers)
	{
		if (Marker)
		{
			Marker->Destroy();
		}
	}
	SpawnedClaimMarkers.Reset();
}

void AGlytchTileManager::LoadBuildingMetadata()
{
	MetadataByUniqueId.Reset();

	FString JsonText;
	const FString MetadataPath = TileData ? TileData->GetActiveMetadataFilePath() : FString();
	if (!FFileHelper::LoadFileToString(JsonText, *ResolveProjectRelativePath(MetadataPath)))
	{
		UE_LOG(LogTemp, Warning, TEXT("Could not read building metadata: %s"), *MetadataPath);
		return;
	}

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("Could not parse building metadata JSON."));
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* Buildings = nullptr;
	if (!Root->TryGetArrayField(TEXT("buildings"), Buildings))
	{
		UE_LOG(LogTemp, Warning, TEXT("Building metadata JSON has no 'buildings' array."));
		return;
	}

	for (const TSharedPtr<FJsonValue>& Value : *Buildings)
	{
		const TSharedPtr<FJsonObject> Object = Value->AsObject();
		if (!Object.IsValid())
		{
			continue;
		}

		FGlytchBuildingMetadataRow Row = RowFromJson(Object);
		if (!Row.UniqueId.IsEmpty())
		{
			MetadataByUniqueId.Add(FName(Row.UniqueId), Row);
		}
	}
}

void AGlytchTileManager::SpawnBuildings()
{
	if (!TileData || !BuildingActorClass)
	{
		return;
	}

	for (const TSoftObjectPtr<UStaticMesh>& MeshPtr : TileData->MassMeshes)
	{
		UStaticMesh* Mesh = MeshPtr.LoadSynchronous();
		if (!Mesh)
		{
			continue;
		}

		const FName UniqueId = ResolveUniqueIdForMesh(Mesh);
		FGlytchBuildingMetadataRow Metadata;
		if (!FindMetadata(UniqueId, Metadata))
		{
			Metadata.UniqueId = UniqueId.ToString();
			Metadata.SourceQuality = TEXT("metadata_missing");
		}

		AGlytchBuildingActor* Building = GetWorld()->SpawnActor<AGlytchBuildingActor>(BuildingActorClass, FVector::ZeroVector, FRotator::ZeroRotator);
		if (Building)
		{
			Building->InitializeBuilding(Mesh, Metadata);
			SpawnedBuildings.Add(Building);
		}
	}
}

void AGlytchTileManager::SpawnCompanionMarkers()
{
	if (!TileData || !CompanionMarkerClass)
	{
		return;
	}

	for (const FGlytchMarkerDefinition& MarkerDef : TileData->CompanionMarkers)
	{
		const FVector Location = TileData->LocalMetersToUnreal(MarkerDef.LocalMeters);
		AGlytchCompanionMarkerActor* Marker = GetWorld()->SpawnActor<AGlytchCompanionMarkerActor>(CompanionMarkerClass, Location, FRotator::ZeroRotator);
		if (Marker)
		{
			Marker->InitializeMarker(MarkerDef.CompanionType);
#if WITH_EDITOR
			Marker->SetActorLabel(MarkerDef.Id.ToString());
#endif
			SpawnedMarkers.Add(Marker);
		}
	}
}

void AGlytchTileManager::SpawnOrderOverlays()
{
	if (!TileData)
	{
		return;
	}

	for (const FGlytchOrderOverlayDefinition& OverlayDef : TileData->OrderOverlays)
	{
		AActor* OverlayActor = GetWorld()->SpawnActor<AActor>(AActor::StaticClass(), TileData->LocalMetersToUnreal(OverlayDef.LocalMeters), FRotator::ZeroRotator);
		if (!OverlayActor)
		{
			continue;
		}

		USceneComponent* Root = NewObject<USceneComponent>(OverlayActor, TEXT("OverlayRoot"));
		Root->RegisterComponent();
		OverlayActor->SetRootComponent(Root);

		UGlytchOrderOverlayComponent* OverlayComponent = NewObject<UGlytchOrderOverlayComponent>(OverlayActor, TEXT("OrderOverlay"));
		OverlayComponent->OrderName = OverlayDef.OrderName;
		OverlayComponent->ExtentMeters = OverlayDef.ExtentMeters;
		OverlayComponent->SetupAttachment(Root);
		OverlayComponent->RegisterComponent();

		UStaticMeshComponent* DebugMesh = NewObject<UStaticMeshComponent>(OverlayActor, TEXT("OrderOverlayDebugMesh"));
		DebugMesh->SetupAttachment(Root);
		DebugMesh->RegisterComponent();
		DebugMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		DebugMesh->SetWorldScale3D(FVector(OverlayDef.ExtentMeters, OverlayDef.ExtentMeters, 1.0f));

		if (UStaticMesh* PlaneMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane")))
		{
			DebugMesh->SetStaticMesh(PlaneMesh);
		}

#if WITH_EDITOR
		OverlayActor->SetActorLabel(OverlayDef.Id.ToString());
#endif
		SpawnedOverlayActors.Add(OverlayActor);
	}
}

void AGlytchTileManager::SpawnClaimMarkers()
{
	if (!TileData || !ClaimMarkerClass || !bSpawnClaimMarkers || MaxClaimMarkers == 0)
	{
		return;
	}

	int32 SpawnedCount = 0;
	for (const TPair<FName, FGlytchBuildingMetadataRow>& Entry : MetadataByUniqueId)
	{
		if (SpawnedCount >= MaxClaimMarkers)
		{
			break;
		}

		const FGlytchBuildingMetadataRow& Metadata = Entry.Value;
		FVector LocalMeters = Metadata.CentroidLocalMeters;
		const float MarkerHeightMeters = FMath::Max(Metadata.HeightP90, Metadata.EstimatedHeight) + 4.0f;
		LocalMeters.Z = FMath::Max(LocalMeters.Z, Metadata.GroundZ) + MarkerHeightMeters;

		AGlytchClaimMarkerActor* Marker = GetWorld()->SpawnActor<AGlytchClaimMarkerActor>(
			ClaimMarkerClass,
			TileData->LocalMetersToUnreal(LocalMeters),
			FRotator::ZeroRotator);
		if (Marker)
		{
			Marker->InitializeClaimMarker(Entry.Key, Metadata.ClaimStatus);
#if WITH_EDITOR
			Marker->SetActorLabel(FString::Printf(TEXT("CLAIM_%s_%s"), *Entry.Key.ToString(), *Marker->ClaimStatus));
#endif
			SpawnedClaimMarkers.Add(Marker);
			++SpawnedCount;
		}
	}
}

void AGlytchTileManager::CreateProxyPlanes()
{
	if (!TileData)
	{
		return;
	}

	const float WidthCm = (TileData->BoundsLocalMeters.MaxX - TileData->BoundsLocalMeters.MinX) * 100.0f;
	const float HeightCm = (TileData->BoundsLocalMeters.MaxY - TileData->BoundsLocalMeters.MinY) * 100.0f;
	const FVector CenterCm(WidthCm * 0.5f, HeightCm * 0.5f, 0.0f);

	if (GroundProxyComponent)
	{
		GroundProxyComponent->SetWorldLocation(CenterCm + FVector(0.0f, 0.0f, -10.0f));
		GroundProxyComponent->SetWorldScale3D(FVector(WidthCm / 100.0f, HeightCm / 100.0f, 1.0f));
	}

	if (WaterProxyComponent)
	{
		WaterProxyComponent->SetWorldLocation(CenterCm);
		WaterProxyComponent->SetWorldScale3D(FVector(WidthCm / 100.0f, HeightCm / 100.0f, 1.0f));
	}
}

FName AGlytchTileManager::ResolveUniqueIdForMesh(UStaticMesh* Mesh) const
{
	if (!Mesh)
	{
		return NAME_None;
	}

	const FString MeshName = Mesh->GetName();
	const FName ExactName(MeshName);
	if (MetadataByUniqueId.Contains(ExactName))
	{
		return ExactName;
	}

	for (const TPair<FName, FGlytchBuildingMetadataRow>& Entry : MetadataByUniqueId)
	{
		if (MeshName.Contains(Entry.Key.ToString()))
		{
			return Entry.Key;
		}
	}

	return ExactName;
}

FString AGlytchTileManager::ResolveProjectRelativePath(const FString& Path) const
{
	if (FPaths::IsRelative(Path))
	{
		return FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), Path);
	}

	return Path;
}
