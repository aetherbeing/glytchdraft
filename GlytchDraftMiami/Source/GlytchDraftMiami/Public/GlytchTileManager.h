#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GlytchTypes.h"
#include "GlytchTileManager.generated.h"

class AGlytchBuildingActor;
class AGlytchClaimMarkerActor;
class AGlytchCompanionMarkerActor;
class UGlytchOrderOverlayComponent;
class UGlytchTileDataAsset;
class UStaticMesh;
class UStaticMeshComponent;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchTileManager : public AActor
{
	GENERATED_BODY()

public:
	AGlytchTileManager();

	virtual void BeginPlay() override;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	TObjectPtr<UGlytchTileDataAsset> TileData;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	TSubclassOf<AGlytchBuildingActor> BuildingActorClass;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	TSubclassOf<AGlytchCompanionMarkerActor> CompanionMarkerClass;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	TSubclassOf<AGlytchClaimMarkerActor> ClaimMarkerClass;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	bool bSpawnOnBeginPlay = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Preview")
	bool bLoadPreviewMetadata = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Claims")
	bool bSpawnClaimMarkers = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Claims", meta = (ClampMin = "0"))
	int32 MaxClaimMarkers = 100;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Runtime")
	TArray<TObjectPtr<AGlytchBuildingActor>> SpawnedBuildings;

	UFUNCTION(CallInEditor, BlueprintCallable, Category = "Glytch|Tile")
	void RebuildTile();

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetMassesVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetCompanionMarkersVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetOrderOverlaysVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetClaimMarkersVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetGroundProxyVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetWaterProxyVisible(bool bVisible);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Layers")
	void SetPointEvidenceVisible(bool bVisible);

	UFUNCTION(BlueprintPure, Category = "Glytch|Metadata")
	bool FindMetadata(FName UniqueId, FGlytchBuildingMetadataRow& OutMetadata) const;

private:
	UPROPERTY()
	TArray<TObjectPtr<AGlytchCompanionMarkerActor>> SpawnedMarkers;

	UPROPERTY()
	TArray<TObjectPtr<AActor>> SpawnedOverlayActors;

	UPROPERTY()
	TArray<TObjectPtr<AGlytchClaimMarkerActor>> SpawnedClaimMarkers;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> GroundProxyComponent;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> WaterProxyComponent;

	TMap<FName, FGlytchBuildingMetadataRow> MetadataByUniqueId;

	void ClearRuntimeActors();
	void LoadBuildingMetadata();
	void SpawnBuildings();
	void SpawnCompanionMarkers();
	void SpawnOrderOverlays();
	void SpawnClaimMarkers();
	void CreateProxyPlanes();
	FName ResolveUniqueIdForMesh(UStaticMesh* Mesh) const;
	FString ResolveProjectRelativePath(const FString& Path) const;
};
