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

void AGlytchMiamiPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);

	if (AGlytchMiamiHUD* MiamiHUD = Cast<AGlytchMiamiHUD>(GetHUD()))
	{
		MiamiHUD->SetHoveredBuilding(GetBuildingUnderCursor());
	}
}

void AGlytchMiamiPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	InputComponent->BindAction(TEXT("Select"), IE_Pressed, this, &AGlytchMiamiPlayerController::SelectBuildingUnderCursor);
	InputComponent->BindAction(TEXT("ToggleMasses"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleMasses);
	InputComponent->BindAction(TEXT("ToggleMarkers"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleMarkers);
	InputComponent->BindAction(TEXT("ToggleOverlays"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleOverlays);
	InputComponent->BindAction(TEXT("ToggleClaims"), IE_Pressed, this, &AGlytchMiamiPlayerController::ToggleClaims);
}

void AGlytchMiamiPlayerController::SelectBuildingUnderCursor()
{
	if (AGlytchMiamiHUD* MiamiHUD = Cast<AGlytchMiamiHUD>(GetHUD()))
	{
		MiamiHUD->SetSelectedBuilding(GetBuildingUnderCursor());
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

void AGlytchMiamiPlayerController::ToggleClaims()
{
	bClaimsVisible = !bClaimsVisible;
	if (AGlytchTileManager* Manager = GetTileManager())
	{
		Manager->SetClaimMarkersVisible(bClaimsVisible);
	}
}

AGlytchBuildingActor* AGlytchMiamiPlayerController::GetBuildingUnderCursor()
{
	FHitResult Hit;
	if (!GetHitResultUnderCursor(ECC_Visibility, false, Hit))
	{
		return nullptr;
	}

	AGlytchBuildingActor* Building = Cast<AGlytchBuildingActor>(Hit.GetActor());
	if (!Building && Hit.GetComponent())
	{
		Building = Cast<AGlytchBuildingActor>(Hit.GetComponent()->GetOwner());
	}

	return Building;
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
