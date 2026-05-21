#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GlytchTypes.h"
#include "GlytchTileDataAsset.generated.h"

class UStaticMesh;

UCLASS(BlueprintType)
class GLYTCHDRAFTMIAMI_API UGlytchTileDataAsset : public UDataAsset
{
	GENERATED_BODY()

public:
	UGlytchTileDataAsset();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Manifest")
	FString ManifestFilePath;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString PreviewMetadataFilePath;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FString FullMetadataFilePath;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	FName TileName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	FString SourceCity;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Tile")
	FString PrimaryNeighborhood;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Spatial")
	FVector LocalOriginShiftMeters = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Spatial")
	FGlytchBoundsMeters BoundsLocalMeters;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Assets")
	TArray<TSoftObjectPtr<UStaticMesh>> MassMeshes;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Assets")
	bool bUsePreviewMetadata = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Markers")
	TArray<FGlytchMarkerDefinition> CompanionMarkers;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	TArray<FGlytchOrderOverlayDefinition> OrderOverlays;

	UFUNCTION(CallInEditor, BlueprintCallable, Category = "Glytch|Manifest")
	bool LoadManifest();

	UFUNCTION(BlueprintPure, Category = "Glytch|Spatial")
	FVector LocalMetersToUnreal(const FVector& LocalMeters) const;

	UFUNCTION(BlueprintPure, Category = "Glytch|Metadata")
	FString GetActiveMetadataFilePath() const;

private:
	FString ResolveProjectRelativePath(const FString& Path) const;
};
