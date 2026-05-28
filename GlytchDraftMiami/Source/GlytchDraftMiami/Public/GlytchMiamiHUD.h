#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "GlytchMiamiHUD.generated.h"

class AGlytchBuildingActor;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchMiamiHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Selection")
	void SetSelectedBuilding(AGlytchBuildingActor* Building);

	UFUNCTION(BlueprintCallable, Category = "Glytch|Selection")
	void SetHoveredBuilding(AGlytchBuildingActor* Building);

	UFUNCTION(BlueprintPure, Category = "Glytch|Selection")
	AGlytchBuildingActor* GetSelectedBuilding() const { return SelectedBuilding.Get(); }

private:
	UPROPERTY()
	TWeakObjectPtr<AGlytchBuildingActor> SelectedBuilding;

	UPROPERTY()
	TWeakObjectPtr<AGlytchBuildingActor> HoveredBuilding;
};
