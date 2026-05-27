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
      .from("trace_balances")
      .select("available_trace, updated_at")
      .eq("user_id", user.id)
      .maybeSingle();

    if (error) {
      return jsonResponse({ error: error.message }, 400);
    }

    return jsonResponse({
      user_id: user.id,
      available_trace: data?.available_trace ?? 0,
      updated_at: data?.updated_at ?? null,
    });
  } catch (error) {
    return jsonResponse({ error: getErrorMessage(error) }, 401);
  }
});
