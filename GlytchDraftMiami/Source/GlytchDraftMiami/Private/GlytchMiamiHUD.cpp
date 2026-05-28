#include "GlytchMiamiHUD.h"

#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "GlytchBuildingActor.h"
#include "GlytchBuildingMetadataComponent.h"

void AGlytchMiamiHUD::DrawHUD()
{
	Super::DrawHUD();

	if (!Canvas)
	{
		return;
	}

	const FString HelpText = TEXT("1 Masses   2 AI Markers   3 Orders   4 Fly/Walk   5 Claims   Hover/click buildings for metadata");
	FCanvasTextItem HelpItem(FVector2D(24.0f, 24.0f), FText::FromString(HelpText), GEngine->GetSmallFont(), FLinearColor::White);
	HelpItem.EnableShadow(FLinearColor::Black);
	Canvas->DrawItem(HelpItem);

	AGlytchBuildingActor* Building = SelectedBuilding.Get();
	const FLinearColor MetadataColor = FLinearColor::Yellow;
	if (!Building || !Building->MetadataComponent)
	{
		Building = HoveredBuilding.Get();
		if (!Building || !Building->MetadataComponent)
		{
			return;
		}
	}

	const FString MetadataText = Building->MetadataComponent->GetDisplayText();
	FCanvasTextItem MetadataItem(FVector2D(24.0f, 58.0f), FText::FromString(MetadataText), GEngine->GetSmallFont(), MetadataColor);
	MetadataItem.EnableShadow(FLinearColor::Black);
	Canvas->DrawItem(MetadataItem);
}

void AGlytchMiamiHUD::SetSelectedBuilding(AGlytchBuildingActor* Building)
{
	if (AGlytchBuildingActor* Previous = SelectedBuilding.Get())
	{
		Previous->SetSelected(false);
	}

	SelectedBuilding = Building;

	if (Building)
	{
		Building->SetSelected(true);
	}
}

void AGlytchMiamiHUD::SetHoveredBuilding(AGlytchBuildingActor* Building)
{
	if (HoveredBuilding.Get() == Building)
	{
		return;
	}

	if (AGlytchBuildingActor* Previous = HoveredBuilding.Get())
	{
		Previous->SetHovered(false);
	}

	HoveredBuilding = Building;

	if (Building)
	{
		Building->SetHovered(true);
	}
}
