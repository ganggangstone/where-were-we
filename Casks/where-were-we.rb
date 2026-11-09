cask "where-were-we" do
  version "0.10.2"
  sha256 "a894a75e13c758b4721611fc0f101ac5f3cfee3c28d5c4a1f9ee5fb9732ea127"

  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{version}/where-were-we_#{version}_aarch64-apple-darwin.zip"
  name "where-were-we"
  desc "Local code structure maps for humans and AI agents"
  homepage "https://github.com/ganggangstone/where-were-we"

  depends_on arch: :arm64
  depends_on formula: ["gh", "git"]
  depends_on macos: :big_sur

  app "where-were-we.app"
end
