#include "GlytchCompanionMarkerActor.h"

#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

AGlytchCompanionMarkerActor::AGlytchCompanionMarkerActor()
{
	PrimaryActorTick.bCanEverTick = false;

	MarkerMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MarkerMesh"));
	SetRootComponent(MarkerMesh);
	MarkerMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MarkerMesh->SetWorldScale3D(FVector(3.0));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereMesh.Succeeded())
	{
		MarkerMesh->SetStaticMesh(SphereMesh.Object);
	}
}

void AGlytchCompanionMarkerActor::InitializeMarker(EGlytchCompanionType InType)
{
	CompanionType = InType;
}
