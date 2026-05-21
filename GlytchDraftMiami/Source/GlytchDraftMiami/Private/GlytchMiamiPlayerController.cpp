#include "GlytchMiamiPlayerController.h"

#include "EngineUtils.h"
#include "GlytchBuildingActor.h"
#include "GlytchMiamiHUD.h"
#include "GlytchTileManager.h"

AGlytchMiamiPlayerController::AGlytchMiamiPlayerController()
{
	bShowMouseCursor = true;
	DefaultMouseCursor = EMouseCursor::Crosshairs;
}

void AGlytchMiamiPlayerController::BeginPlay()
{
	Super::BeginPlay();
	SetInputMode(FInputModeGameAndUI());
}

void AGlytchMiamiPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	InputComponent->BindAction(TEXT("Select"), IE_Pressed, this, &AGlytchMiamiPlayerController::SelectBuildingUnderCursor);
	InputComponent->BindAction(TEXT("ToggleMasses"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleMasses);
	InputComponent->BindAction(TEXT("ToggleMarkers"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleMarkers);
	InputComponent->BindAction(TEXT("ToggleOverlays"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleOverlays);
}

void AGlytchMiamiPlayerController::SelectBuildingUnderCursor()
{
	FHitResult Hit;
	if (!GetHitResultUnderCursor(ECC_Visibility, false, Hit))
	{
		return;
	}

	AGlytchBuildingActor* Building = Cast<AGlytchBuildingActor>(Hit.GetActor());
	if (!Building && Hit.GetComponent())
	{
		Building = Cast<AGlytchBuildingActor>(Hit.GetComponent()->GetOwner());
	}

	if (AGlytchMiamiHUD* MiamiHUD = Cast<AGlytchMiamiHUD>(GetHUD()))
	{
		MiamiHUD->SetSelectedBuilding(Building);
	}
}

void AGlytchMiamiPlayerController::ToggleMasses()
{
	bMassesVisible = !bMassesVisible;
	if (AGlytchTileManager* Manager = GetTileManager())
	{
		Manager->SetMassesVisible(bMassesVisible);
	}
}

void AGlytchMiamiPlayerController::ToggleMarkers()
{
	bMarkersVisible = !bMarkersVisible;
	if (AGlytchTileManager* Manager = GetTileManager())
	{
		Manager->SetCompanionMarkersVisible(bMarkersVisible);
	}
}

void AGlytchMiamiPlayerController::ToggleOverlays()
{
	bOverlaysVisible = !bOverlaysVisible;
	if (AGlytchTileManager* Manager = GetTileManager())
	{
		Manager->SetOrderOverlaysVisible(bOverlaysVisible);
	}
}

AGlytchTileManager* AGlytchMiamiPlayerController::GetTileManager()
{
	if (CachedTileManager.IsValid())
	{
		return CachedTileManager.Get();
	}

	for (TActorIterator<AGlytchTileManager> It(GetWorld()); It; ++It)
	{
		CachedTileManager = *It;
		return *It;
	}

	return nullptr;
}
