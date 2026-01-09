class Repr < Formula
  desc "Privacy-first CLI that analyzes git repositories and generates developer profiles"
  homepage "https://repr.dev"
  version "0.2.11"
  
  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/repr-app/cli/releases/download/v0.2.11/repr-macos.tar.gz"
      sha256 "de43548fa4cde34dc17a0033d70c109a6dda35b9f8df73a34ac830160d3b9c13"
    else
      url "https://github.com/repr-app/cli/releases/download/v0.2.11/repr-macos.tar.gz"
      sha256 "de43548fa4cde34dc17a0033d70c109a6dda35b9f8df73a34ac830160d3b9c13"
    end
  end

  on_linux do
    url "https://github.com/repr-app/cli/releases/download/v0.2.11/repr-linux.tar.gz"
    sha256 "07c0390104dfb2518f4f5cb2b9b138d7abd16d8b38ab249ebd793e85b4e8428a"
  end

  def install
    bin.install "repr"
  end

  test do
    system "#{bin}/repr", "--help"
    system "#{bin}/repr", "config", "--json"
  end
end


