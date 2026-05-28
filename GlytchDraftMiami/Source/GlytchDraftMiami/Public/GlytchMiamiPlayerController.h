#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "GlytchMiamiPlayerController.generated.h"

class AGlytchTileManager;
class AGlytchBuildingActor;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchMiamiPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AGlytchMiamiPlayerController();

	virtual void BeginPlay() override;
	virtual void PlayerTick(float DeltaTime) override;
	virtual void SetupInputComponent() override;

private:
	bool bMassesVisible = true;
	bool bMarkersVisible = true;
	bool bOverlaysVisible = true;
	bool bClaimsVisible = true;

	UPROPERTY()
	TWeakObjectPtr<AGlytchTileManager> CachedTileManager;

	void SelectBuildingUnderCursor();
	void ToggleMasses();
	void ToggleMarkers();
	void ToggleOverlays();
	void ToggleClaims();
	AGlytchBuildingActor* GetBuildingUnderCursor();
	AGlytchTileManager* GetTileManager();
};
