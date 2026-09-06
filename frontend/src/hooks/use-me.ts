import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type Me } from "@/lib/api";

export function useMe() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    api
      .me()
      .then(setMe)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          setMe(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(refresh, [refresh]);

  return { me, loading, refresh };
}