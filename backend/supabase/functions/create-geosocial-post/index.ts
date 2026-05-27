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

  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const user = await getAuthenticatedUser(req);
    const body = await req.json();
    const coordinates = body.coordinates ?? {};
    const postBody = String(body.body ?? "").trim();
    const structureId = body.structure_id ? String(body.structure_id).trim() : null;
    const tileId = body.tile_id ? String(body.tile_id).trim() : null;
    const latitude = body.latitude ?? coordinates.lat ?? null;
    const longitude = body.longitude ?? coordinates.lng ?? null;
    const visibility = String(body.visibility ?? "public").trim();

    if (!postBody) {
      return jsonResponse({ error: "body is required" }, 400);
    }

    if (!structureId && !tileId && (latitude === null || longitude === null)) {
      return jsonResponse({ error: "structure_id, tile_id, or coordinates are required" }, 400);
    }

    if (!["public", "unlisted", "friends", "private"].includes(visibility)) {
      return jsonResponse({ error: "visibility must be public, unlisted, friends, or private" }, 400);
    }

    const supabase = createServiceClient();
    const { data, error } = await supabase.rpc("create_geosocial_post", {
      p_user_id: user.id,
      p_body: postBody,
      p_structure_id: structureId,
      p_tile_id: tileId,
      p_latitude: latitude,
      p_longitude: longitude,
      p_visibility: visibility,
      p_media: body.media ?? [],
      p_provenance: body.provenance ?? {},
    });

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({ post: data }, 201);
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
