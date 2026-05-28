#include "GlytchClaimMarkerActor.h"

#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

AGlytchClaimMarkerActor::AGlytchClaimMarkerActor()
{
	PrimaryActorTick.bCanEverTick = false;

	MarkerMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ClaimMarkerMesh"));
	SetRootComponent(MarkerMesh);
	MarkerMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MarkerMesh->SetWorldScale3D(FVector(1.25f));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded())
	{
		MarkerMesh->SetStaticMesh(SphereMesh.Object);
	}
}

void AGlytchClaimMarkerActor::InitializeClaimMarker(FName InBuildingUniqueId, const FString& InClaimStatus)
{
	BuildingUniqueId = InBuildingUniqueId;
	ClaimStatus = InClaimStatus.IsEmpty() ? TEXT("open") : InClaimStatus;
}
