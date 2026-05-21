#include "GlytchFlyPawn.h"

#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"

AGlytchFlyPawn::AGlytchFlyPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessPlayer = EAutoReceiveInput::Player0;

	CameraComponent = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	SetRootComponent(CameraComponent);
}

void AGlytchFlyPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	FRotator NewRotation = GetActorRotation();
	NewRotation.Yaw += PendingLook.Yaw * LookSensitivity;
	NewRotation.Pitch = FMath::Clamp(NewRotation.Pitch + PendingLook.Pitch * LookSensitivity, -89.0f, 89.0f);
	SetActorRotation(NewRotation);
	PendingLook = FRotator::ZeroRotator;

	if (!PendingMovement.IsNearlyZero())
	{
		float SpeedMultiplier = 1.0f;
		if (const APlayerController* PC = Cast<APlayerController>(GetController()))
		{
			SpeedMultiplier = PC->IsInputKeyDown(EKeys::LeftShift) ? FastMoveMultiplier : 1.0f;
		}

		FVector WorldMovement =
			GetActorForwardVector() * PendingMovement.X +
			GetActorRightVector() * PendingMovement.Y +
			FVector::UpVector * PendingMovement.Z;
		if (bWalkMode)
		{
			WorldMovement.Z = 0.0f;
		}

		AddActorWorldOffset(WorldMovement.GetClampedToMaxSize(1.0f) * MoveSpeedCmPerSecond * SpeedMultiplier * DeltaSeconds, true);
		PendingMovement = FVector::ZeroVector;
	}
}

void AGlytchFlyPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	PlayerInputComponent->BindAxis(TEXT("MoveForward"), this, &AGlytchFlyPawn::MoveForward);
	PlayerInputComponent->BindAxis(TEXT("MoveRight"), this, &AGlytchFlyPawn::MoveRight);
	PlayerInputComponent->BindAxis(TEXT("MoveUp"), this, &AGlytchFlyPawn::MoveUp);
	PlayerInputComponent->BindAxis(TEXT("Turn"), this, &AGlytchFlyPawn::Turn);
	PlayerInputComponent->BindAxis(TEXT("LookUp"), this, &AGlytchFlyPawn::LookUp);
	PlayerInputComponent->BindAction(TEXT("ToggleWalkMode"), IE_Pressed, this, &AGlytchFlyPawn::ToggleWalkMode);
}

void AGlytchFlyPawn::MoveForward(float Value)
{
	PendingMovement.X = Value;
}

void AGlytchFlyPawn::MoveRight(float Value)
{
	PendingMovement.Y = Value;
}

void AGlytchFlyPawn::MoveUp(float Value)
{
	PendingMovement.Z = bWalkMode ? 0.0f : Value;
}

void AGlytchFlyPawn::Turn(float Value)
{
	PendingLook.Yaw = Value;
}

void AGlytchFlyPawn::LookUp(float Value)
{
	PendingLook.Pitch = Value;
}

void AGlytchFlyPawn::ToggleWalkMode()
{
	bWalkMode = !bWalkMode;

	if (bWalkMode)
	{
		FVector Location = GetActorLocation();
		Location.Z = FMath::Max(Location.Z, WalkHeightCm);
		SetActorLocation(Location);
	}
}
