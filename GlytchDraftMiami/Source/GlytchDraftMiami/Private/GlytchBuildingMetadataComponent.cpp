#include "GlytchBuildingMetadataComponent.h"

UGlytchBuildingMetadataComponent::UGlytchBuildingMetadataComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UGlytchBuildingMetadataComponent::SetMetadata(const FGlytchBuildingMetadataRow& InMetadata)
{
	Metadata = InMetadata;
}

FString UGlytchBuildingMetadataComponent::GetDisplayText() const
{
	return FString::Printf(
		TEXT("UNIQUEID: %s\nheight_p90: %.2f m\nground_z: %.2f m\nsource_quality: %s"),
		*Metadata.UniqueId,
		Metadata.HeightP90,
		Metadata.GroundZ,
		*Metadata.SourceQuality);
}
