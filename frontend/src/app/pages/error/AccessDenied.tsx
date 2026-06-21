import { Link } from "react-router";
import { Button } from "../../components/ui/button";

export function AccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-2">
      <h1 className="text-2xl font-bold text-red-600">403 - Forbidden</h1>
      <p className="text-muted-foreground text-sm">
        You do not have permission to view this resource.
      </p>
      <Button variant="outline" className="mt-2" asChild>
        <Link to="/">Go Home</Link>
      </Button>
    </div>
  );
}
