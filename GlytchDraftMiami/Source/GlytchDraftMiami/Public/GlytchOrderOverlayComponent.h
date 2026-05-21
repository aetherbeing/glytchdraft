#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "GlytchTypes.h"
#include "GlytchOrderOverlayComponent.generated.h"

UCLASS(ClassGroup = (Glytch), meta = (BlueprintSpawnableComponent))
class GLYTCHDRAFTMIAMI_API UGlytchOrderOverlayComponent : public USceneComponent
{
	GENERATED_BODY()

public:
	UGlytchOrderOverlayComponent();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	EGlytchOrderName OrderName = EGlytchOrderName::Unknown;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Orders")
	float ExtentMeters = 400.0f;
};
