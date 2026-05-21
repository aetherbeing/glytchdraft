#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "GlytchMiamiPlayerController.generated.h"

class AGlytchTileManager;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchMiamiPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AGlytchMiamiPlayerController();

	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;

private:
	bool bMassesVisible = true;
	bool bMarkersVisible = true;
	bool bOverlaysVisible = true;

	UPROPERTY()
	TWeakObjectPtr<AGlytchTileManager> CachedTileManager;

	void SelectBuildingUnderCursor();
	void ToggleMasses();
	void ToggleMarkers();
	void ToggleOverlays();
	AGlytchTileManager* GetTileManager();
};
