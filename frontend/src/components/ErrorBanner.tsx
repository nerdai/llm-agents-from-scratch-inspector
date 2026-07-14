interface ErrorBannerProps {
  message: string;
}

function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <strong>Request failed:</strong> {message}
    </div>
  );
}

export default ErrorBanner;
