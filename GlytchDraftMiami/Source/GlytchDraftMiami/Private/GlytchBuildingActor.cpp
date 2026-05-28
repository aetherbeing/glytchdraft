#include "GlytchBuildingActor.h"

#include "Components/StaticMeshComponent.h"
#include "GlytchBuildingMetadataComponent.h"

AGlytchBuildingActor::AGlytchBuildingActor()
{
	PrimaryActorTick.bCanEverTick = false;

	MeshComponent = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BuildingMesh"));
	SetRootComponent(MeshComponent);
	MeshComponent->SetCollisionProfileName(TEXT("BlockAll"));
	MeshComponent->SetGenerateOverlapEvents(false);

	MetadataComponent = CreateDefaultSubobject<UGlytchBuildingMetadataComponent>(TEXT("BuildingMetadata"));
}

void AGlytchBuildingActor::InitializeBuilding(UStaticMesh* Mesh, const FGlytchBuildingMetadataRow& Metadata)
{
	UniqueId = FName(Metadata.UniqueId);
	MeshComponent->SetStaticMesh(Mesh);
	MetadataComponent->SetMetadata(Metadata);
#if WITH_EDITOR
	SetActorLabel(Metadata.UniqueId);
#endif
}

void AGlytchBuildingActor::SetSelected(bool bSelected)
{
	bIsSelected = bSelected;
	UpdateHighlight();
}

void AGlytchBuildingActor::SetHovered(bool bHovered)
{
	bIsHovered = bHovered;
	UpdateHighlight();
}

void AGlytchBuildingActor::UpdateHighlight()
{
	const bool bHighlighted = bIsSelected || bIsHovered;
	MeshComponent->SetRenderCustomDepth(bHighlighted);
	MeshComponent->SetCustomDepthStencilValue(bIsSelected ? 1 : 2);
}
