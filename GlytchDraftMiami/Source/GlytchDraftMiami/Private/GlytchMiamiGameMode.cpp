#include "GlytchMiamiGameMode.h"

#include "GlytchFlyPawn.h"
#include "GlytchMiamiHUD.h"
#include "GlytchMiamiPlayerController.h"

AGlytchMiamiGameMode::AGlytchMiamiGameMode()
{
	DefaultPawnClass = AGlytchFlyPawn::StaticClass();
	PlayerControllerClass = AGlytchMiamiPlayerController::StaticClass();
	HUDClass = AGlytchMiamiHUD::StaticClass();
}
