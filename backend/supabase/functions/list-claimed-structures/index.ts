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
    const supabase = createServiceClient();
    const { data, error } = await supabase
      .from("structure_claim_status")
      .select("structure_id, tile_id, address, label, latitude, longitude, trace_cost, structure_provenance, claim_id, owner_user_id, owner_display_name, order_id, claim_status, claim_cost_trace, claimed_at, released_at")
      .eq("owner_user_id", user.id)
      .order("claimed_at", { ascending: false });

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({ claimed_structures: data ?? [] });
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
