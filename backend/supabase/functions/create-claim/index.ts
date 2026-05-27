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
    const structureId = String(body.structure_id ?? "").trim();
    const coordinates = body.coordinates ?? {};

    if (!structureId) {
      return jsonResponse({ error: "structure_id is required" }, 400);
    }

    const supabase = createServiceClient();
    const { data, error } = await supabase.rpc("create_structure_claim", {
      p_user_id: user.id,
      p_structure_id: structureId,
      p_order_id: body.order_id ?? null,
      p_structure_provenance: body.structure_provenance ?? {},
      p_tile_id: body.tile_id ?? null,
      p_address: body.address ?? null,
      p_label: body.label ?? null,
      p_latitude: body.latitude ?? coordinates.lat ?? null,
      p_longitude: body.longitude ?? coordinates.lng ?? null,
    });

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({ claim: data }, 201);
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
