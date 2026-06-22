
import { Link } from "react-router";
import { Button } from "../../components/ui/button";

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-2">
      <h1 className="text-2xl font-bold text-foreground">404 - Not Found</h1>
      <p className="text-muted-foreground text-sm">
        The page you're looking for doesn't exist.
      </p>
      <Button variant="outline" className="mt-2" asChild>
        <Link to="/">Go Home</Link>
      </Button>
    </div>
  );
}