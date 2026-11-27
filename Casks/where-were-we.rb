cask "where-were-we" do
  version "0.11.0"
  sha256 "e24f739c9d827f67885483bf43aeea5f283141143b4fcfcdbfd6fca14b4360cd"

  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{version}/where-were-we_#{version}_aarch64-apple-darwin.zip"
  name "where-were-we"
  desc "Local code structure maps for humans and AI agents"
  homepage "https://github.com/ganggangstone/where-were-we"

  depends_on arch: :arm64
  depends_on formula: ["gh", "git"]
  depends_on macos: :big_sur

  app "where-were-we.app"
end
