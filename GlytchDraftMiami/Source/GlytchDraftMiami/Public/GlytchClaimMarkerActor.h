#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GlytchClaimMarkerActor.generated.h"

class UStaticMeshComponent;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchClaimMarkerActor : public AActor
{
	GENERATED_BODY()

public:
	AGlytchClaimMarkerActor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Claim")
	TObjectPtr<UStaticMeshComponent> MarkerMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Claim")
	FName BuildingUniqueId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Claim")
	FString ClaimStatus;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Claim")
	void InitializeClaimMarker(FName InBuildingUniqueId, const FString& InClaimStatus);
};
