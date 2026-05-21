#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "GlytchFlyPawn.generated.h"

class UCameraComponent;

UCLASS()
class GLYTCHDRAFTMIAMI_API AGlytchFlyPawn : public APawn
{
	GENERATED_BODY()

public:
	AGlytchFlyPawn();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Glytch|Camera")
	TObjectPtr<UCameraComponent> CameraComponent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Glytch|Camera")
	float MoveSpeedCmPerSecond = 12000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Glytch|Camera")
	float FastMoveMultiplier = 4.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Glytch|Camera")
	float LookSensitivity = 0.12f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Glytch|Camera")
	bool bWalkMode = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Glytch|Camera")
	float WalkHeightCm = 180.0f;

	UFUNCTION(BlueprintCallable, Category = "Glytch|Camera")
	void ToggleWalkMode();

private:
	FVector PendingMovement = FVector::ZeroVector;
	FRotator PendingLook = FRotator::ZeroRotator;

	void MoveForward(float Value);
	void MoveRight(float Value);
	void MoveUp(float Value);
	void Turn(float Value);
	void LookUp(float Value);
};
