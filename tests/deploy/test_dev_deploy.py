"""개발 배포 job: 이미지 준비(prepare-dev-image.sh), ECR 푸시(push-dev-image.sh), 개발 Lambda 이미지 교체(update-dev-lambda.sh)."""

import unittest

from tests.deploy.harness import SandboxTestCase

ECR = "551372961758.dkr.ecr.ap-northeast-2.amazonaws.com/cking-comment-filter"
REGISTRY = "551372961758.dkr.ecr.ap-northeast-2.amazonaws.com"
FUNCTION = "dev-cking-comment-filter"
DIGEST = "sha256:" + "a" * 64
CURRENT = "sha256:" + "c" * 64
NOT_FOUND = "An error occurred (ImageNotFoundException) when calling the DescribeImages operation: not found\n"
FAKE_BUILD = '#!/usr/bin/env bash\necho "$@" > "$FAKE_STATE/build-image.args"\n'


class PrepareImageTest(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.sha = self.sb.commit({"server/app.py": "app"})
        self.tag = self.sha[:12]
        build = self.sb.repo / "scripts" / "build-image.sh"
        build.parent.mkdir(parents=True, exist_ok=True)
        build.write_text(FAKE_BUILD)
        build.chmod(0o755)
        self.sb.on("ecr", "get-login-password", stdout="password\n")

    def run_step(self):
        return self.sb.run("prepare-dev-image.sh", {"ECR_REPOSITORY": ECR, "GITHUB_SHA": self.sha})

    def built(self):
        path = self.sb.state / "build-image.args"
        return path.read_text() if path.exists() else None

    def test_커밋_태그가_있으면_올려_둔_이미지를_받는다(self):
        self.sb.on("ecr", "describe-images", f"imageTag={self.tag}", stdout=DIGEST + "\n")
        r = self.run_step()
        self.assertEqual(r.code, 0)
        login = r.docker("login")
        self.assertEqual(login[0], ["login", "--username", "AWS", "--password-stdin", REGISTRY])
        self.assertEqual([c for c in r.calls if c["prog"] == "docker"][0]["stdin"], "password\n")
        self.assertEqual(r.docker("pull"), [["pull", f"{ECR}@{DIGEST}"]])
        self.assertEqual(r.docker("tag"), [["tag", f"{ECR}@{DIGEST}", "filter:check"]])
        self.assertEqual(r.aws("describe-images")[0][2:4], ["--repository-name", "cking-comment-filter"])
        self.assertEqual(r.outputs, {"digest": DIGEST})
        self.assertIsNone(self.built())

    def test_커밋_태그가_없으면_새로_빌드한다(self):
        self.sb.on("ecr", "describe-images", stderr=NOT_FOUND, code=254)
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(self.built(), "filter:check\n")
        self.assertEqual(r.docker("pull"), [])
        self.assertEqual(r.outputs, {})

    def test_ECR_조회_오류는_멈춘다(self):
        err = "An error occurred (AccessDeniedException) when calling the DescribeImages operation: denied\n"
        self.sb.on("ecr", "describe-images", stderr=err, code=254)
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(err, r.stdout)
        self.assertIsNone(self.built())
        self.assertEqual(r.outputs, {})


class PushImageTest(SandboxTestCase):
    def test_새_이미지를_푸시하고_digest를_출력한다(self):
        sha = self.sb.commit({"server/app.py": "app"})
        self.sb.on("ecr", "describe-images", f"imageTag={sha[:12]}", stdout=DIGEST + "\n")
        r = self.sb.run("push-dev-image.sh", {"ECR_REPOSITORY": ECR, "GITHUB_SHA": sha})
        self.assertEqual(r.code, 0)
        self.assertEqual(r.docker("tag"), [["tag", "filter:check", f"{ECR}:{sha[:12]}"]])
        self.assertEqual(r.docker("push"), [["push", f"{ECR}:{sha[:12]}"]])
        self.assertEqual(r.outputs, {"digest": DIGEST})


class UpdateDevLambdaTest(SandboxTestCase):
    def setUp(self):
        super().setUp()
        self.old = self.sb.commit({"server/app.py": "1"})
        self.head = self.sb.commit({"server/app.py": "2"})
        self.newer = self.sb.commit({"server/app.py": "3"})
        self.sb.git("checkout", "-q", "-b", "other", self.old)
        self.diverged = self.sb.commit({"server/app.py": "other"})
        self.sb.git("checkout", "-q", "develop")

    def deployed(self, *tags):
        self.sb.on("lambda", "get-function", stdout=f"{ECR}@{CURRENT}\n")
        self.sb.on("ecr", "describe-images", f"imageDigest={CURRENT}", stdout="\t".join(tags) + "\n")
        self.sb.on("lambda", "update-function-code", stdout="InProgress\n")
        self.sb.on("lambda", "wait", "function-updated-v2")

    def run_step(self):
        return self.sb.run("update-dev-lambda.sh", {
            "ECR_REPOSITORY": ECR, "FUNCTION_NAME": FUNCTION, "DIGEST": DIGEST, "GITHUB_SHA": self.head,
        })

    def image_line(self):
        return f"이미지: {ECR}:{self.head[:12]} ({DIGEST})\n"

    def assert_updated(self, r, before):
        self.assertEqual(r.code, 0)
        self.assertEqual(r.aws("update-function-code"), [[
            "lambda", "update-function-code", "--function-name", FUNCTION,
            "--image-uri", f"{ECR}@{DIGEST}", "--query", "LastUpdateStatus", "--output", "text",
        ]])
        self.assertEqual(len(r.aws("wait", "function-updated-v2")), 1)
        self.assertEqual(r.summary, self.image_line() + f"개발 Lambda 이미지 교체: {before} -> {self.head[:12]} ({DIGEST})\n")

    def assert_not_updated(self, r):
        self.assertEqual(r.aws("update-function-code"), [])

    def test_개발_Lambda가_없으면_건너뛴다(self):
        self.sb.on("lambda", "get-function", stderr="An error occurred (ResourceNotFoundException) when calling the GetFunction operation\n", code=254)
        r = self.run_step()
        self.assertEqual(r.code, 0)
        self.assertEqual(r.summary, self.image_line() + "개발 Lambda가 아직 없어 이미지 교체를 건너뛴다\n")
        self.assert_not_updated(r)

    def test_Lambda_조회_오류는_멈춘다(self):
        err = "An error occurred (AccessDeniedException) when calling the GetFunction operation\n"
        self.sb.on("lambda", "get-function", stderr=err, code=254)
        r = self.run_step()
        self.assertEqual(r.code, 1)
        self.assertIn(err, r.stdout)
        self.assert_not_updated(r)

    def test_배포된_커밋이_조상이면_교체한다(self):
        self.deployed(self.old[:12])
        self.assert_updated(self.run_step(), self.old[:12])

    def test_같은_커밋이면_교체한다(self):
        self.deployed(self.head[:12])
        self.assert_updated(self.run_step(), self.head[:12])

    def test_조상과_같은_커밋_태그가_함께면_교체한다(self):
        self.deployed(self.old[:12], self.head[:12])
        self.assert_updated(self.run_step(), f"{self.old[:12]} {self.head[:12]}")

    def test_prod_태그와_다른_태그는_보지_않는다(self):
        self.deployed(f"prod-{self.newer[:12]}", self.old[:12], "latest")
        self.assert_updated(self.run_step(), self.old[:12])

    def assert_newer_skips(self, r, newer):
        msg = f"더 새 커밋 {newer} 이 배포되어 있어 이미지 교체를 건너뛴다"
        self.assertEqual(r.code, 0)
        self.assertIn(f"::warning::{msg}", r.stdout)
        self.assertEqual(r.summary, self.image_line() + msg + "\n")
        self.assert_not_updated(r)

    def test_더_새_커밋이_배포돼_있으면_건너뛴다(self):
        self.deployed(self.newer[:12])
        self.assert_newer_skips(self.run_step(), self.newer[:12])

    def test_옛_커밋과_더_새_커밋_태그는_순서와_관계없이_건너뛴다(self):
        for tags in ((self.old[:12], self.newer[:12]), (self.newer[:12], self.old[:12])):
            with self.subTest(tags=tags):
                self.sb.rules.clear()
                self.deployed(*tags)
                self.assert_newer_skips(self.run_step(), self.newer[:12])

    def assert_fails(self, r, error):
        self.assertEqual(r.code, 1)
        self.assertIn(f"::error::{error}", r.stdout)
        self.assert_not_updated(r)

    def test_갈라진_커밋이면_멈춘다(self):
        self.deployed(self.diverged[:12])
        self.assert_fails(self.run_step(), f"배포된 커밋 {self.diverged[:12]} 과 이 커밋의 이력이 갈라졌다")

    def test_더_새_커밋과_갈라진_커밋_태그는_순서와_관계없이_멈춘다(self):
        for tags in ((self.newer[:12], self.diverged[:12]), (self.diverged[:12], self.newer[:12])):
            with self.subTest(tags=tags):
                self.sb.rules.clear()
                self.deployed(*tags)
                self.assert_fails(self.run_step(), f"배포된 커밋 {self.diverged[:12]} 과 이 커밋의 이력이 갈라졌다")

    def test_이력에_없는_커밋이면_멈춘다(self):
        self.deployed("0123456789ab")
        self.assert_fails(self.run_step(), f"배포된 이미지 {ECR}@{CURRENT} 의 커밋을 확인할 수 없다")

    def test_이력에_없는_커밋이_섞여_있으면_멈춘다(self):
        self.deployed(self.old[:12], "0123456789ab")
        self.assert_fails(self.run_step(), f"배포된 이미지 {ECR}@{CURRENT} 의 커밋을 확인할 수 없다")

    def test_배포된_이미지에_커밋_태그가_없으면_멈춘다(self):
        self.deployed("None")
        self.assert_fails(self.run_step(), f"배포된 이미지 {ECR}@{CURRENT} 의 커밋을 확인할 수 없다")

    def test_배포된_이미지가_ECR에_없으면_멈춘다(self):
        self.sb.on("lambda", "get-function", stdout=f"{ECR}@{CURRENT}\n")
        self.sb.on("ecr", "describe-images", stderr=NOT_FOUND, code=254)
        self.assert_fails(self.run_step(), f"배포된 이미지 {ECR}@{CURRENT} 의 커밋을 확인할 수 없다")


if __name__ == "__main__":
    unittest.main()
