#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GlytchTypes.h"
#include "GlytchCompanionMarkerActor.generated.h"

class UStaticMeshComponent;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchCompanionMarkerActor : public AActor
{
	GENERATED_BODY()

public:
	AGlytchCompanionMarkerActor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Marker")
	TObjectPtr<UStaticMeshComponent> MarkerMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Marker")
	EGlytchCompanionType CompanionType = EGlytchCompanionType::Unknown;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Marker")
	void InitializeMarker(EGlytchCompanionType InType);
};
