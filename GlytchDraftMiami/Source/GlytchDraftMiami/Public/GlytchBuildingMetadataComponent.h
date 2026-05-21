#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GlytchTypes.h"
#include "GlytchBuildingMetadataComponent.generated.h"

UCLASS(ClassGroup = (Glytch), meta = (BlueprintSpawnableComponent))
class GLYTCHDRAFTMIAMI_API UGlytchBuildingMetadataComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UGlytchBuildingMetadataComponent();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glytch|Metadata")
	FGlytchBuildingMetadataRow Metadata;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Metadata")
	void SetMetadata(const FGlytchBuildingMetadataRow& InMetadata);

	UFUNCTION(BlueprintPure, Category = "Glytch|Metadata")
	FString GetDisplayText() const;
};
