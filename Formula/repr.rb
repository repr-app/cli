class Repr < Formula
  desc "Privacy-first CLI that analyzes git repositories and generates developer profiles"
  homepage "https://repr.dev"
  version "0.2.0"
  
  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/repr-app/cli/releases/download/v0.2.0/repr-macos.tar.gz"
      sha256 "PLACEHOLDER_ARM64_SHA256"
    else
      url "https://github.com/repr-app/cli/releases/download/v0.2.0/repr-macos.tar.gz"
      sha256 "PLACEHOLDER_X86_64_SHA256"
    end
  end

  on_linux do
    url "https://github.com/repr-app/cli/releases/download/v0.2.0/repr-linux.tar.gz"
    sha256 "PLACEHOLDER_LINUX_SHA256"
  end

  def install
    bin.install "repr"
  end

  test do
    system "#{bin}/repr", "--help"
    system "#{bin}/repr", "config", "--json"
  end
end

