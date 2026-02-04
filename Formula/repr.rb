class Repr < Formula
  desc "Privacy-first CLI that analyzes git repositories and generates developer profiles"
  homepage "https://repr.dev"
  version "0.2.18"
  
  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/repr-app/cli/releases/download/v0.2.18/repr-macos.tar.gz"
      sha256 "79562b16a3c23c4924d4f4d97e8fdb7e1f71df660efd3156216bd435d8a66bf3"
    else
      url "https://github.com/repr-app/cli/releases/download/v0.2.18/repr-macos.tar.gz"
      sha256 "79562b16a3c23c4924d4f4d97e8fdb7e1f71df660efd3156216bd435d8a66bf3"
    end
  end

  on_linux do
    url "https://github.com/repr-app/cli/releases/download/v0.2.18/repr-linux.tar.gz"
    sha256 "6778c2b8c8761e4bab947a2beb5488958ea5baa8f34ea6da57c53dd999d8d9d2"
  end

  def install
    bin.install "repr"
  end

  test do
    system "#{bin}/repr", "--help"
    system "#{bin}/repr", "config", "--json"
  end
end