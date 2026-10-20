cask "where-were-we" do
  version "0.4.0"
  sha256 "96e37519f8fe504fbe72e6739d354b0c0452299d772a7c656d3778ad5d50d13c"

  url "https://github.com/ganggangstone/where-were-we/releases/download/v#{version}/where-were-we_#{version}_aarch64-apple-darwin.zip"
  name "where-were-we"
  desc "Local code structure maps for humans and AI agents"
  homepage "https://github.com/ganggangstone/where-were-we"

  depends_on arch: :arm64
  depends_on formula: ["gh", "git"]
  depends_on macos: :big_sur

  app "where-were-we.app"
end
