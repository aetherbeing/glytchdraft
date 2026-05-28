#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GlytchTypes.h"
#include "GlytchBuildingActor.generated.h"

class UGlytchBuildingMetadataComponent;
class UStaticMeshComponent;
class UStaticMesh;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchBuildingActor : public AActor
{
	GENERATED_BODY()

public:
	AGlytchBuildingActor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Building")
	TObjectPtr<UStaticMeshComponent> MeshComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Building")
	TObjectPtr<UGlytchBuildingMetadataComponent> MetadataComponent;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Building")
	FName UniqueId;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Building")
	void InitializeBuilding(UStaticMesh* Mesh, const FGlytchBuildingMetadataRow& Metadata);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Building")
	void SetSelected(bool bSelected);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Building")
	void SetHovered(bool bHovered);

private:
	bool bIsSelected = false;
	bool bIsHovered = false;

	void UpdateHighlight();
};
