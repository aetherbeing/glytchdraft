import {
  createServiceClient,
  getErrorMessage,
  getAuthenticatedUser,
  handleOptions,
  jsonResponse,
} from "../_shared/supabase.ts";

Deno.serve(async (req) => {
  const optionsResponse = handleOptions(req);
  if (optionsResponse) return optionsResponse;

  if (req.method !== "GET") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const user = await getAuthenticatedUser(req);

    const url = new URL(req.url);
    const structureId = url.searchParams.get("structure_id")?.trim();
    const tileId = url.searchParams.get("tile_id")?.trim();

    if (!structureId && !tileId) {
      return jsonResponse({ error: "structure_id or tile_id is required" }, 400);
    }

    const supabase = createServiceClient();
    let structuresQuery = supabase
      .from("structure_claim_status")
      .select("*")
      .order("structure_id", { ascending: true });

    if (structureId) {
      structuresQuery = structuresQuery.eq("structure_id", structureId);
    } else if (tileId) {
      structuresQuery = structuresQuery.eq("tile_id", tileId);
    }

    const { data: structures, error: structuresError } = await structuresQuery;
    if (structuresError) {
      return jsonResponse({ error: structuresError.message }, 400);
    }

    let postsQuery = supabase
      .from("geosocial_posts")
      .select("id, user_id, structure_id, tile_id, latitude, longitude, body, visibility, media, reactions, comments_count, provenance, created_at")
      .or(`visibility.in.(public,unlisted),user_id.eq.${user.id}`)
      .order("created_at", { ascending: false })
      .limit(50);

    const selectedTileId = tileId ?? structures?.[0]?.tile_id ?? null;

    if (structureId && selectedTileId) {
      postsQuery = postsQuery.or(`structure_id.eq.${structureId},tile_id.eq.${selectedTileId}`);
    } else if (structureId) {
      postsQuery = postsQuery.eq("structure_id", structureId);
    } else if (tileId) {
      postsQuery = postsQuery.eq("tile_id", tileId);
    }

    const { data: posts, error: postsError } = await postsQuery;
    if (postsError) {
      return jsonResponse({ error: postsError.message }, 400);
    }

    let claimHistory: unknown[] = [];
    if (structureId) {
      const { data: history, error: historyError } = await supabase
        .from("claim_history")
        .select("claim_id, structure_id, previous_status, new_status, event_type, created_at")
        .eq("structure_id", structureId)
        .order("created_at", { ascending: false })
        .limit(25);

      if (historyError) {
        return jsonResponse({ error: historyError.message }, 400);
      }

      claimHistory = history ?? [];
    }

    return jsonResponse({
      structures: structures ?? [],
      selected_structure: structures?.[0] ?? null,
      nearby_posts: posts ?? [],
      claim_history: claimHistory,
    });
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
