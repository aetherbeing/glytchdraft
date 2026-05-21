#include "GlytchTileDataAsset.h"

#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	float GetNumberField(const TSharedPtr<FJsonObject>& Object, const TCHAR* FieldName, float DefaultValue = 0.0f)
	{
		double Value = DefaultValue;
		return Object.IsValid() && Object->TryGetNumberField(FieldName, Value) ? static_cast<float>(Value) : DefaultValue;
	}

	FVector ReadVectorArray(const TArray<TSharedPtr<FJsonValue>>& Values)
	{
		const double X = Values.IsValidIndex(0) ? Values[0]->AsNumber() : 0.0;
		const double Y = Values.IsValidIndex(1) ? Values[1]->AsNumber() : 0.0;
		const double Z = Values.IsValidIndex(2) ? Values[2]->AsNumber() : 0.0;
		return FVector(X, Y, Z);
	}

	EGlytchCompanionType CompanionTypeFromId(const FString& Id)
	{
		if (Id.Contains(TEXT("field_guide"))) return EGlytchCompanionType::FieldGuide;
		if (Id.Contains(TEXT("atmosphere_voice"))) return EGlytchCompanionType::AtmosphereVoice;
		if (Id.Contains(TEXT("data_steward"))) return EGlytchCompanionType::DataSteward;
		if (Id.Contains(TEXT("architectural_envisioner"))) return EGlytchCompanionType::ArchitecturalEnvisioner;
		if (Id.Contains(TEXT("cinematic_director"))) return EGlytchCompanionType::CinematicDirector;
		if (Id.Contains(TEXT("order_chronicler"))) return EGlytchCompanionType::OrderChronicler;
		return EGlytchCompanionType::Unknown;
	}
}

UGlytchTileDataAsset::UGlytchTileDataAsset()
{
	ManifestFilePath = TEXT("../exports/miami_hero_tile/metadata/tile_manifest.json");
	PreviewMetadataFilePath = TEXT("../exports/miami_hero_tile_preview/preview_20_buildings_metadata.json");
	FullMetadataFilePath = TEXT("../exports/miami_hero_tile/metadata/buildings_metadata.json");
	TileName = TEXT("miami_hero_tile_v001");
	SourceCity = TEXT("Miami");
	PrimaryNeighborhood = TEXT("Key Biscayne");
	LocalOriginShiftMeters = FVector(581000.0, 2839000.0, 0.0);
}

bool UGlytchTileDataAsset::LoadManifest()
{
	FString JsonText;
	if (!FFileHelper::LoadFileToString(JsonText, *ResolveProjectRelativePath(ManifestFilePath)))
	{
		UE_LOG(LogTemp, Warning, TEXT("GlytchTileDataAsset could not read manifest: %s"), *ManifestFilePath);
		return false;
	}

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("GlytchTileDataAsset could not parse manifest JSON."));
		return false;
	}

	TileName = FName(Root->GetStringField(TEXT("tile_name")));
	SourceCity = Root->GetStringField(TEXT("source_city"));

	const TSharedPtr<FJsonObject>* Location = nullptr;
	if (Root->TryGetObjectField(TEXT("real_world_location"), Location) && Location && Location->IsValid())
	{
		(*Location)->TryGetStringField(TEXT("primary_neighborhood"), PrimaryNeighborhood);
	}

	const TSharedPtr<FJsonObject>* Shift = nullptr;
	if (Root->TryGetObjectField(TEXT("local_origin_shift"), Shift) && Shift && Shift->IsValid())
	{
		LocalOriginShiftMeters = FVector(
			GetNumberField(*Shift, TEXT("shift_x")),
			GetNumberField(*Shift, TEXT("shift_y")),
			GetNumberField(*Shift, TEXT("shift_z")));
	}

	const TSharedPtr<FJsonObject>* Bounds = nullptr;
	if (Root->TryGetObjectField(TEXT("bounds_local_meters"), Bounds) && Bounds && Bounds->IsValid())
	{
		BoundsLocalMeters.MinX = GetNumberField(*Bounds, TEXT("min_x"));
		BoundsLocalMeters.MinY = GetNumberField(*Bounds, TEXT("min_y"));
		BoundsLocalMeters.MaxX = GetNumberField(*Bounds, TEXT("max_x"), 4652.0f);
		BoundsLocalMeters.MaxY = GetNumberField(*Bounds, TEXT("max_y"), 3923.0f);
		BoundsLocalMeters.MinZ = GetNumberField(*Bounds, TEXT("min_z_approx"), -2.0f);
		BoundsLocalMeters.MaxZ = GetNumberField(*Bounds, TEXT("max_z_approx"), 84.0f);
	}

	CompanionMarkers.Reset();
	const TSharedPtr<FJsonObject>* Markers = nullptr;
	if (Root->TryGetObjectField(TEXT("ai_companion_marker_positions_local_meters"), Markers) && Markers && Markers->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Entry : (*Markers)->Values)
		{
			const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
			if (Entry.Value->TryGetArray(Position))
			{
				FGlytchMarkerDefinition Marker;
				Marker.Id = FName(Entry.Key);
				Marker.CompanionType = CompanionTypeFromId(Entry.Key);
				Marker.LocalMeters = ReadVectorArray(*Position);
				CompanionMarkers.Add(Marker);
			}
		}
	}

	OrderOverlays.Reset();
	const TSharedPtr<FJsonObject>* Orders = nullptr;
	if (Root->TryGetObjectField(TEXT("order_overlay_positions_local_meters"), Orders) && Orders && Orders->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Entry : (*Orders)->Values)
		{
			const TSharedPtr<FJsonObject> OrderObject = Entry.Value->AsObject();
			if (!OrderObject.IsValid())
			{
				continue;
			}

			const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
			if (!OrderObject->TryGetArrayField(TEXT("position"), Position))
			{
				continue;
			}

			FGlytchOrderOverlayDefinition Order;
			Order.Id = FName(Entry.Key);
			Order.LocalMeters = ReadVectorArray(*Position);
			Order.ExtentMeters = GetNumberField(OrderObject, TEXT("extent_m"), 400.0f);

			if (Entry.Key.Contains(TEXT("pink_opaque")))
			{
				Order.OrderName = EGlytchOrderName::PinkOpaque;
				OrderOverlays.Add(Order);
			}
			else if (Entry.Key.Contains(TEXT("mirrorsweat")))
			{
				Order.Id = TEXT("order_cradle_mold_field");
				Order.OrderName = EGlytchOrderName::CradleMold;
				OrderOverlays.Add(Order);
			}
		}
	}

	return true;
}

FVector UGlytchTileDataAsset::LocalMetersToUnreal(const FVector& LocalMeters) const
{
	return LocalMeters * 100.0;
}

FString UGlytchTileDataAsset::GetActiveMetadataFilePath() const
{
	return bUsePreviewMetadata ? PreviewMetadataFilePath : FullMetadataFilePath;
}

FString UGlytchTileDataAsset::ResolveProjectRelativePath(const FString& Path) const
{
	if (FPaths::IsRelative(Path))
	{
		return FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(), Path);
	}

	return Path;
}
